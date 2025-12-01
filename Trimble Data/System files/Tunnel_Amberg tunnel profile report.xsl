<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt">

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
                    NaN="?"
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

<xsl:variable name="Pi" select="3.14159265358979323846264"/>
<xsl:variable name="halfPi" select="$Pi div 2.0"/>

<xsl:variable name="DegreesSymbol" select="'.'"/>
<xsl:variable name="MinutesSymbol" select="''"/>
<xsl:variable name="SecondsSymbol" select="''"/>

<xsl:variable name="fileExt" select="'dat'"/>

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

  <!-- Select the FieldBook node to process -->
  <xsl:apply-templates select="JOBFile/FieldBook" />

</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">

  <xsl:for-each select="TunnelCrossSectionRecord">
    <xsl:variable name="stn" select="Station"/>
    <xsl:variable name="xsTimeStamp" select="@TimeStamp"/>

    <xsl:if test="count(following-sibling::TunnelCrossSectionRecord[Station = $stn]) = 0"> <!-- Only output the details for the last profile taken at this station -->
      <xsl:for-each select="TunnelPointDeltaRecord">
        <xsl:variable name="obsID" select="ObservationID"/>
        <xsl:if test="/JOBFile/FieldBook/PointRecord[@ID = $obsID]/Deleted = 'false'">  <!-- Referenced point is not deleted -->
          <!-- Only deal with a point if it is the first occurance of this point (to maintain the order) -->
          <xsl:if test="count(preceding-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) = 0">
            <!-- Now we want to make sure that we use the last set of values available for a point -->
            <xsl:choose>
              <xsl:when test="count(following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) &gt; 0">
                <!-- Get the details for the last deltas record for this point -->
                <xsl:for-each select="following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')][last()]">
                  <xsl:call-template name="OutputDateAndTime">
                    <xsl:with-param name="timeStamp" select="$xsTimeStamp"/>
                  </xsl:call-template>
                  <xsl:value-of select="format-number(($stn + DeltaStation) * $DistConvFactor, $DecPl3, 'Standard')"/>
                  <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->
                  <xsl:value-of select="format-number(HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
                  <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->
                  <xsl:value-of select="format-number(VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
                </xsl:for-each>
              </xsl:when>
              <xsl:otherwise>  <!-- This is the one and only delta record for this point -->
                <xsl:call-template name="OutputDateAndTime">
                  <xsl:with-param name="timeStamp" select="$xsTimeStamp"/>
                </xsl:call-template>
                <xsl:value-of select="format-number(($stn + DeltaStation) * $DistConvFactor, $DecPl3, 'Standard')"/>
                <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->
                <xsl:value-of select="format-number(HorizontalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
                <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->
                <xsl:value-of select="format-number(VerticalOffset * $DistConvFactor, $DecPl3, 'Standard')"/>
              </xsl:otherwise>
            </xsl:choose>
            <xsl:call-template name="NewLine"/>
          </xsl:if>
        </xsl:if>
      </xsl:for-each>
    </xsl:if>
  </xsl:for-each>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* Output date and time ********************* -->
<!-- **************************************************************** -->
<xsl:template name="OutputDateAndTime">
  <xsl:param name="timeStamp"/>
  
  <xsl:value-of select="substring($timeStamp, 6, 2)"/>
  <xsl:text>.</xsl:text>
  <xsl:value-of select="substring($timeStamp, 9, 2)"/>
  <xsl:text>.</xsl:text>
  <xsl:value-of select="substring($timeStamp, 1, 4)"/>
  <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->
  
  <xsl:value-of select="substring-after($timeStamp, 'T')"/>
  <xsl:text>&#09;</xsl:text>    <!-- Output tab separator -->

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


</xsl:stylesheet>