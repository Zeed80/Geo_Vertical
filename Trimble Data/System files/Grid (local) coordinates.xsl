<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="text" omit-xml-declaration="yes" encoding="ISO-8859-1"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN=""
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="fileExt" select="'csv'"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->
<xsl:variable name="userField1" select="'outputType|Output|stringMenu|2|Computed local grid coordinates|Entered local grid coordinates'"/>
<xsl:variable name="outputType" select="'Computed local grid coordinates'"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <!-- Output an initial line identifying the columns -->
  <xsl:text>Name,Entered as,</xsl:text>
  <xsl:choose>
    <xsl:when test="$NECoords = 'true'">Grid (local) North, Grid (local) East, Grid (local) Elevation, Transformation name, Grid North, Grid East, Grid Elevation, Code</xsl:when>
    <xsl:otherwise>Grid (local) East, Grid (local) North, Grid (local) Elevation, Transformation name, Grid East, Grid North, Grid Elevation, Code</xsl:otherwise>
  </xsl:choose>
  <xsl:call-template name="NewLine"/>

  <!-- Select FieldBook node to process -->
  <xsl:apply-templates select="JOBFile/FieldBook" />

</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** FieldBook Node Processing ******************* -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
  <xsl:variable name="displayTransformationName" select="PointRecord[ComputedLocalGrid][1]/ComputedLocalGrid/ReferenceTransformation"/>

  <!-- Output the point details in the following two cases:                                                  -->
  <!--   1. Computed local grids are to be output and there is a ComputedLocalGrid element for the point, or -->
  <!--      there is an entered local grid coordinate (LocalGrid element) and the transformation assigned    -->
  <!--      to the local grid position is the same as the current output transformation.                     -->
  <!--   2. Computed local grids are not to be output and the point has entered local grid values (there is  -->
  <!--      a LocalGrid element present in the PointRecord.                                                  -->
  <xsl:apply-templates select="PointRecord[(($outputType = 'Computed local grid coordinates') and
                                            (ComputedLocalGrid or (LocalGrid and LocalGrid/ReferenceTransformation = $displayTransformationName))) or
                                           (($outputType != 'Computed local grid coordinates') and LocalGrid)]"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** FieldBook PointRecord Output ******************* -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord">

  <!-- Output name first -->
  <xsl:value-of select="Name"/>
  <xsl:text>,</xsl:text>

  <xsl:choose>
    <xsl:when test="Grid">Grid,</xsl:when>
    <xsl:when test="LocalGrid">Local,</xsl:when>
  </xsl:choose>
  
  <xsl:variable name="localGridN">
    <xsl:choose>
      <xsl:when test="(($outputType != 'Computed local grid coordinates') and LocalGrid)">
        <xsl:value-of select="LocalGrid/North"/>
      </xsl:when>
      <xsl:when test="ComputedLocalGrid">
        <xsl:value-of select="ComputedLocalGrid/North"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="LocalGrid/North"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="localGridE">
    <xsl:choose>
      <xsl:when test="(($outputType != 'Computed local grid coordinates') and LocalGrid)">
        <xsl:value-of select="LocalGrid/East"/>
      </xsl:when>
      <xsl:when test="ComputedLocalGrid">
        <xsl:value-of select="ComputedLocalGrid/East"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="LocalGrid/East"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="localGridElev">
    <xsl:choose>
      <xsl:when test="(($outputType != 'Computed local grid coordinates') and LocalGrid)">
        <xsl:value-of select="LocalGrid/Elevation"/>
      </xsl:when>
      <xsl:when test="ComputedLocalGrid">
        <xsl:value-of select="ComputedLocalGrid/Elevation"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="LocalGrid/Elevation"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Output the north and east local grid coordinates -->
  <xsl:choose>
    <xsl:when test="$NECoords = 'true'">
      <xsl:value-of select="format-number($localGridN * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
      <xsl:value-of select="format-number($localGridE * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number($localGridE * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
      <xsl:value-of select="format-number($localGridN * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
    </xsl:otherwise>
  </xsl:choose>

  <!-- Output the local elevation value -->
  <xsl:value-of select="format-number($localGridElev * $DistConvFactor, $DecPl3, 'Standard')"/>
  <xsl:text>,</xsl:text>

  <!-- Output the transformation name -->
  <xsl:choose>
    <xsl:when test="(($outputType != 'Computed local grid coordinates') and LocalGrid)">
      <xsl:value-of select="LocalGrid/ReferenceTransformation"/>
    </xsl:when>
    <xsl:when test="ComputedLocalGrid">
      <xsl:value-of select="ComputedLocalGrid/ReferenceTransformation"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="LocalGrid/ReferenceTransformation"/>
    </xsl:otherwise>
  </xsl:choose>
  <xsl:text>,</xsl:text>

  <xsl:variable name="gridN">
    <xsl:choose>
      <xsl:when test="ComputedGrid">
        <xsl:value-of select="ComputedGrid/North"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Grid/North"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="gridE">
    <xsl:choose>
      <xsl:when test="ComputedGrid">
        <xsl:value-of select="ComputedGrid/East"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Grid/East"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="gridElev">
    <xsl:choose>
      <xsl:when test="ComputedGrid">
        <xsl:value-of select="ComputedGrid/Elevation"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="Grid/Elevation"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Output the north and east grid coordinates -->
  <xsl:choose>
    <xsl:when test="$NECoords = 'true'">
      <xsl:value-of select="format-number($gridN * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
      <xsl:value-of select="format-number($gridE * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="format-number($gridE * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
      <xsl:value-of select="format-number($gridN * $DistConvFactor, $DecPl3, 'Standard')"/>
      <xsl:text>,</xsl:text>
    </xsl:otherwise>
  </xsl:choose>

  <!-- Output the grid elevation value -->
  <xsl:value-of select="format-number($gridElev * $DistConvFactor, $DecPl3, 'Standard')"/>
  <xsl:text>,</xsl:text>

  <!-- Output the code -->
  <xsl:value-of select="Code"/>

  <xsl:call-template name="NewLine"/> <!-- New line ready for next point -->
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


</xsl:stylesheet>