<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" >

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

<xsl:variable name="DegreesSymbol" select="'.'"/>
<xsl:variable name="MinutesSymbol" select="''"/>
<xsl:variable name="SecondsSymbol" select="''"/>

<xsl:variable name="fileExt" select="'raw'"/>

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

<xsl:variable name="userField1" select="'includePtCoords|Include point coordinates|StringMenu|2|Yes|No'"/>
<xsl:variable name="includePtCoords" select="'Yes'"/>
<xsl:variable name="includePointCoords">
  <xsl:if test="$includePtCoords = 'Yes'">1</xsl:if>  <!-- Create a standard boolean value to use for later test purposes -->
  <xsl:if test="$includePtCoords != 'Yes'">0</xsl:if>
</xsl:variable>

<!-- Define key to speed up search for target ht details -->
<xsl:key name="tgtHtID-search" match="//JOBFile/FieldBook/TargetRecord" use="@ID"/>
<xsl:key name="stnID-search" match="//JOBFile/FieldBook/StationRecord" use="@ID"/>
<xsl:key name="atmosID-search" match="//JOBFile/FieldBook/AtmosphereRecord" use="@ID"/>
<xsl:key name="resectPt-search" match="//JOBFile/FieldBook/PointRecord" use="Name"/>
<xsl:key name="reducedPoint-search" match="//JOBFile/Reductions/Point" use="Name"/>

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
  <xsl:value-of select="'50='"/>
  <xsl:value-of select="JOBFile/@jobName"/>
  <xsl:call-template name="NewLine"/>
  <xsl:if test="JOBFile/@TimeStamp != ''">  <!-- Could be null string on an upgraded job -->
    <!-- Output the date and time details from the time stamp on the JOBFile record -->
    <xsl:value-of select="'51='"/>
    <xsl:value-of select="substring-before(JOBFile/@TimeStamp, 'T')"/>
    <xsl:call-template name="NewLine"/>
    <xsl:value-of select="'52='"/>
    <xsl:value-of select="substring-after(JOBFile/@TimeStamp, 'T')"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

  <!-- Output a '23=' units record defining the units of the data in the file -->
  <xsl:value-of select="'23='"/>
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">4</xsl:when> <!-- Output as hPa -->
    <xsl:when test="$PressUnit='InchHg'">3</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">2</xsl:when>
    <xsl:otherwise>1</xsl:otherwise> <!-- mbar (same as hPa as default) -->
  </xsl:choose>
  <xsl:choose>
    <xsl:when test="$TempUnit='Celsius'">1</xsl:when>
    <xsl:otherwise>2</xsl:otherwise> <!-- Fahrenheit -->
  </xsl:choose>
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1</xsl:when>
    <xsl:otherwise>2</xsl:otherwise> <!-- Feet or US Feet GDM file doesn't differentiate -->
  </xsl:choose>
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">2</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">4</xsl:when>
    <xsl:otherwise>3</xsl:otherwise>  <!-- Decimal degrees -->
  </xsl:choose>
  <xsl:call-template name="NewLine"/>

  <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />

</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
<!-- Process the records under the FieldBook node in the order encountered -->
  <xsl:for-each select="*">
    <xsl:choose>
      <!-- Handle Point record -->
      <xsl:when test="name(current()) = 'PointRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>

      <!-- Handle Station record -->
      <xsl:when test="name(current()) = 'StationRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>

      <!-- Handle BackBearing record -->
      <xsl:when test="name(current()) = 'BackBearingRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>

      <!-- Handle Atmosphere record -->
      <xsl:when test="name(current()) = 'AtmosphereRecord'">
        <xsl:apply-templates select="current()"/>
      </xsl:when>

      <!-- Handle Target record -->
      <xsl:when test="name(current()) = 'TargetRecord'">
        <xsl:apply-templates select="current()"/>
      </xsl:when>

      <!-- Handle Instrument record -->
      <xsl:when test="name(current()) = 'InstrumentRecord'">
        <xsl:apply-templates select="current()"/>
      </xsl:when>
    </xsl:choose>

    <!-- Process any notes attached to the current record -->
    <xsl:if test="current()/Notes">
      <xsl:apply-templates select="current()/Notes"/>
    </xsl:if>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** Reductions Node Processing ******************* -->
<!-- **************************************************************** -->
<xsl:template match="Reductions">
  <xsl:apply-templates select="Point"/> 
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord">
  <xsl:if test="Deleted = 'false'">  <!-- only output if not deleted -->
    <xsl:if test="Grid">
      <xsl:call-template name="GridPoint"/>
    </xsl:if>

    <xsl:if test="Circle">
      <xsl:call-template name="Observation"/> 
    </xsl:if>

  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Grid Point Details Output ********************* -->
<!-- **************************************************************** -->
<xsl:template name="GridPoint">
  <xsl:if test="Method != 'Resection'"> <!-- Already picked up on station output -->
    <xsl:variable name="NthStr" select="format-number(Grid/North * $DistConvFactor, $DecPl3, 'Standard')"/>

    <xsl:variable name="EastStr" select="format-number(Grid/East * $DistConvFactor, $DecPl3, 'Standard')"/>

    <xsl:variable name="ElevStr" select="format-number(Grid/Elevation * $DistConvFactor, $DecPl3, 'Standard')"/>

    <xsl:value-of select="concat('5=', Name)"/>
    <xsl:call-template name="NewLine"/>
    <xsl:if test="string-length(Code) != 0">
      <xsl:value-of select="concat('4=', Code)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="$NthStr != '?'">
      <xsl:value-of select="concat('37=', $NthStr)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="$EastStr != '?'">
      <xsl:value-of select="concat('38=', $EastStr)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="$ElevStr != '?'">
      <xsl:value-of select="concat('39=', $ElevStr)"/> 
      <xsl:call-template name="NewLine"/>
    </xsl:if>

    <xsl:if test="Features">  <!-- Point has Features and Attributes -->
      <xsl:apply-templates select="Features"/>
    </xsl:if>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- **************** Observation Details Output ******************** -->
<!-- **************************************************************** -->
<xsl:template name="Observation">
  <xsl:variable name="RecordID">
    <xsl:value-of select="@ID" />
  </xsl:variable>

  <xsl:variable name="HzStr">
    <xsl:call-template name="AngleValue">
      <xsl:with-param name="TheAngle">
        <xsl:value-of select="Circle/HorizontalCircle"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="VtStr">
    <xsl:call-template name="AngleValue">
      <xsl:with-param name="TheAngle">
        <xsl:value-of select="Circle/VerticalCircle"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="TgtStr">
    <xsl:variable name="TH">
      <xsl:for-each select="key('tgtHtID-search', TargetID)[1]">
        <xsl:value-of select="TargetHeight"/>
      </xsl:for-each>
    </xsl:variable>
    <xsl:value-of select="format-number($TH * $DistConvFactor, $DecPl3, 'Standard')"/>
  </xsl:variable>

  <xsl:variable name="PrismConst">
    <xsl:variable name="PC">
      <xsl:for-each select="key('tgtHtID-search', TargetID)[1]">
        <xsl:value-of select="PrismConstant"/>
      </xsl:for-each>
    </xsl:variable>
    <xsl:choose>
      <xsl:when test="$PC = ''">  <!-- In case of null value set to zero -->
        <xsl:value-of select="0"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$PC * $DistConvFactor"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="Atmosppm">
    <xsl:variable name="ppm">
      <xsl:for-each select="key('stnID-search', StationID)">
        <xsl:for-each select="key('atmosID-search', AtmosphereID)">
          <xsl:value-of select="PPM"/>
        </xsl:for-each>
      </xsl:for-each>
    </xsl:variable>
    <xsl:choose>
      <xsl:when test="string(number($ppm))='NaN'"><xsl:value-of select="'0'"/></xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$ppm"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="StnSF">
    <xsl:variable name="SF">
      <xsl:for-each select="key('stnID-search', StationID)">
        <xsl:value-of select="ScaleFactor"/>
      </xsl:for-each>
    </xsl:variable>
    <xsl:choose>
      <!-- Don't apply the computed station scale factor to backsight obs - they were used to compute it! -->
      <xsl:when test="(string(number($SF))='NaN') or (Classification = 'BackSight')"><xsl:value-of select="'1'"/></xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$SF"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="SDStr">
    <xsl:variable name="SD" select="Circle/EDMDistance" />
    <!-- Apply the prism constant, atmospheric ppm correction and station scale factor to the slope dist -->
    <xsl:choose>
      <xsl:when test="string(number($SD))='NaN'"><xsl:value-of select="'?'"/></xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="format-number(($SD * $DistConvFactor + $PrismConst + ($Atmosppm div 1000000.0 * ($SD  * $DistConvFactor))) * $StnSF, $DecPl3, 'Standard')"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Set the hz angle and vt angle labels according to observation face -->
  <xsl:variable name="HzLbl">
    <xsl:choose>
      <xsl:when test="Circle/VerticalCircle &lt; 180">
        <xsl:value-of select="'7'"/>
      </xsl:when>
      <xsl:otherwise><xsl:value-of select="'17'"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  
  <xsl:variable name="VtLbl">
    <xsl:choose>
      <xsl:when test="Circle/VerticalCircle &lt; 180">
        <xsl:value-of select="'8'"/>
      </xsl:when>
      <xsl:otherwise><xsl:value-of select="'18'"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:value-of select="concat('5=', Name)"/>
  <xsl:call-template name="NewLine"/>
  <xsl:if test="string-length(Code) != 0">
    <xsl:value-of select="concat('4=', Code)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  <xsl:if test="$TgtStr != '?'">
    <xsl:value-of select="concat('6=', $TgtStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  <xsl:if test="$HzStr != '?'">
    <xsl:value-of select="concat($HzLbl, '=', $HzStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  <xsl:if test="$VtStr != '?'">
    <xsl:value-of select="concat($VtLbl, '=', $VtStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  <xsl:if test="$SDStr != '?'">
    <xsl:value-of select="concat('9=', $SDStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

  <xsl:if test="ComputedGrid and ($includePointCoords != 0)"> <!-- There is a ComputedGrid node and we want the coordinates output -->
    <xsl:if test="ComputedGrid/North != ''">
      <xsl:value-of select="concat('37=', format-number(ComputedGrid/North * $DistConvFactor, $DecPl3, 'Standard'))"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="ComputedGrid/East != ''">
      <xsl:value-of select="concat('38=', format-number(ComputedGrid/East * $DistConvFactor, $DecPl3, 'Standard'))"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="ComputedGrid/Elevation != ''">
      <xsl:value-of select="concat('39=', format-number(ComputedGrid/Elevation * $DistConvFactor, $DecPl3, 'Standard'))"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
  </xsl:if>

  <xsl:if test="Features">  <!-- Point has Features and Attributes -->
    <xsl:apply-templates select="Features"/>
  </xsl:if>

  <!-- Output any stakeout grid deltas available for the point -->
  <xsl:if test="Stakeout/GridDeltas">
    <xsl:variable name="dNorth">
      <xsl:variable name="dN" select="Stakeout/GridDeltas/DeltaNorth"/>
        <xsl:choose>
          <xsl:when test="string(number($dN))='NaN'"><xsl:value-of select="'?'"/></xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="format-number($dN * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:otherwise>
        </xsl:choose>
    </xsl:variable>

    <xsl:variable name="dEast">
      <xsl:variable name="dE" select="Stakeout/GridDeltas/DeltaEast"/>
        <xsl:choose>
          <xsl:when test="string(number($dE))='NaN'"><xsl:value-of select="'?'"/></xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="format-number($dE * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:otherwise>
        </xsl:choose>
    </xsl:variable>

    <xsl:variable name="dElev">
      <xsl:variable name="dEl" select="Stakeout/GridDeltas/DeltaElevation"/>
        <xsl:choose>
          <xsl:when test="string(number($dEl))='NaN'"><xsl:value-of select="'?'"/></xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="format-number($dEl * $DistConvFactor, $DecPl3, 'Standard')"/>
          </xsl:otherwise>
        </xsl:choose>
    </xsl:variable>
    
    <xsl:if test="$dNorth != '?'">
      <xsl:value-of select="concat('40=', $dNorth)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="$dEast != '?'">
      <xsl:value-of select="concat('41=', $dEast)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
    <xsl:if test="$dElev != '?'">
      <xsl:value-of select="concat('42=', $dElev)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
  </xsl:if>

  <!-- If this is a Single Distance Offset method point output the original -->
  <!-- observation details as notes following the other point data          -->
  <xsl:if test="(Method = 'DistanceOffset') and DistanceOffset">
    <xsl:variable name="OrigHzStr">
      <xsl:call-template name="AngleValue">
        <xsl:with-param name="TheAngle">
          <xsl:value-of select="DistanceOffset/RawObservation/HorizontalCircle"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:variable name="OrigVtStr">
      <xsl:call-template name="AngleValue">
        <xsl:with-param name="TheAngle">
          <xsl:value-of select="DistanceOffset/RawObservation/VerticalCircle"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>
	
    <xsl:variable name="OrigSDStr">
      <xsl:variable name="SD" select="DistanceOffset/RawObservation/EDMDistance" />
      <!-- Just output the distance as stored without applying the prism constant, -->
      <!-- atmospheric ppm correction and station scale factor                     -->
      <xsl:value-of select="format-number($SD, $DecPl3, 'Standard')"/>
    </xsl:variable>
	
    <xsl:variable name="DirStr" select="DistanceOffset/Direction"/>
	
    <xsl:variable name="OffsetDistStr">
      <xsl:variable name="Dist" select="DistanceOffset/Distance"/>
      <xsl:value-of select="format-number($Dist, $DecPl3, 'Standard')"/>
    </xsl:variable>
	
    <xsl:value-of select="concat('0=Dist Offset: Pt: ', Name, ', Hz: ', $OrigHzStr, ', Vt: ', $OrigVtStr, ', SD: ', $OrigSDStr)"/>
    <xsl:call-template name="NewLine"/>
    <xsl:value-of select="concat('0=Dist Offset: Pt: ', Name, ', Dir: ', $DirStr, ', Dist: ', $OffsetDistStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** AtmosphereRecord Output ********************* -->
<!-- **************************************************************** -->
<xsl:template match="AtmosphereRecord">

  <xsl:variable name="TempStr">
    <xsl:variable name="Temp" select="Temperature" />
    <xsl:choose>
      <xsl:when test="string(number($Temp))='NaN'"><xsl:value-of select="'?'"/></xsl:when> <!-- could use &#160; for space -->
      <xsl:otherwise>
        <xsl:choose>
          <xsl:when test="$TempUnit='Fahrenheit'">
            <xsl:value-of select="format-number($Temp * 1.8 + 32, $DecPl1, 'Standard')"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="format-number($Temp, $DecPl1, 'Standard')"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  <xsl:if test="$TempStr != '?'">
    <xsl:value-of select="concat('56=', $TempStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

  <xsl:variable name="PressStr">
    <xsl:variable name="Press" select="Pressure" />
    <xsl:choose>
      <xsl:when test="string(number($Press))='NaN'"><xsl:value-of select="'?'"/></xsl:when> <!-- could use &#160; for space -->
      <xsl:otherwise>
        <xsl:value-of select="format-number($Press * $PressConvFactor, $DecPl2, 'Standard')"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  <xsl:if test="$PressStr != '?'">
    <xsl:value-of select="concat('74=', $PressStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  
  <xsl:variable name="ppmStr">
    <xsl:variable name="ppm" select="PPM" />
    <xsl:choose>
      <xsl:when test="string(number($ppm))='NaN'"><xsl:value-of select="'?'"/></xsl:when> <!-- could use &#160; for space -->
      <xsl:otherwise><xsl:value-of select="format-number($ppm, $DecPl0, 'Standard')"/></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  <xsl:if test="$ppmStr != '?'">
    <xsl:value-of select="concat('30=', $ppmStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

  <xsl:variable name="RefracStr">
    <xsl:variable name="Refrac">
      <xsl:choose>
        <xsl:when test="RefractionCoefficient">
          <xsl:value-of select="RefractionCoefficient"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:value-of select="Refraction"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:value-of select="format-number($Refrac, $DecPl3, 'Standard')"/>
  </xsl:variable>
  <xsl:if test="$RefracStr != '?'">
    <xsl:value-of select="'58=6372000.000'"/> <!-- Output default earth radius associated with refractive const -->
    <xsl:call-template name="NewLine"/>
    <xsl:value-of select="concat('59=', $RefracStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************* TargetRecord Output ********************** -->
<!-- **************************************************************** -->
<xsl:template match="TargetRecord">
  <!-- Output the prism constant from the TargetRecord -->
  <xsl:variable name="PrismConstStr">
    <xsl:variable name="PC" select="PrismConstant" />
    <xsl:choose>
      <xsl:when test="string(number($PC))='NaN'"><xsl:value-of select="'?'"/></xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="format-number($PC * $DistConvFactor, $DecPl3, 'Standard')"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>
  <xsl:if test="$PrismConstStr != '?'">
    <xsl:value-of select="concat('33=', $PrismConstStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
  
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************* InstrumentRecord Output ******************** -->
<!-- **************************************************************** -->
<xsl:template match="InstrumentRecord">
  <!-- Output the instrument type as a note record -->
  <xsl:value-of select="'0=Instrument: '"/>
  <xsl:value-of select="Type"/>
  <xsl:call-template name="NewLine"/>
  
  <!-- Output the instrument serial number (if present) as a 55= record -->
  <xsl:if test="string-length(Serial) &gt; 0">
    <xsl:value-of select="'55='"/>
    <xsl:value-of select="Serial"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** StationRecord Output ********************** -->
<!-- **************************************************************** -->
<xsl:template match="StationRecord">
  <xsl:variable name="StnStr">
    <xsl:value-of select="StationName" />
  </xsl:variable>

  <xsl:variable name="InstHtStr">
    <xsl:variable name="InstHt" select="TheodoliteHeight" />
    <xsl:value-of select="format-number($InstHt * $DistConvFactor, $DecPl3, 'Standard')" />
  </xsl:variable>

  <xsl:variable name="StnSF">
    <xsl:variable name="SF" select="ScaleFactor" />
    <xsl:choose>
      <xsl:when test="string(number($SF))='NaN'"><xsl:value-of select="'1'"/></xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="format-number($SF, $DecPl8, 'Standard')"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:value-of select="concat('2=', $StnStr)"/>
  <xsl:call-template name="NewLine"/>

  <!-- Output the point code for the station if found in the Reductions section -->
  <xsl:for-each select="key('reducedPoint-search', $StnStr)">
    <xsl:if test="Code != ''">
      <xsl:value-of select="concat('4=', Code)"/>
      <xsl:call-template name="NewLine"/>
    </xsl:if>
  </xsl:for-each>
  
  <xsl:if test="$InstHtStr != '?'">
    <xsl:value-of select="concat('3=', $InstHtStr)"/>
    <xsl:call-template name="NewLine"/>
  </xsl:if>

  <!-- If this is a resected station search for the computed coordinates for the point -->
  <xsl:if test="(StationType = 'StandardResection') or (StationType = 'HelmertResection')">
    <xsl:for-each select="key('resectPt-search', $StnStr)">
      <xsl:if test="Method='Resection'">
        <xsl:variable name="NthStr">
          <xsl:variable name="North" select="Grid/North" />
          <xsl:value-of select="format-number($North * $DistConvFactor, $DecPl3, 'Standard')" />
        </xsl:variable>

        <xsl:variable name="EastStr">
          <xsl:variable name="East" select="Grid/East" />
          <xsl:value-of select="format-number($East * $DistConvFactor, $DecPl3, 'Standard')" />
        </xsl:variable>

        <xsl:variable name="ElevStr">
          <xsl:variable name="Elev" select="Grid/Elevation" />
          <xsl:value-of select="format-number($Elev * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:variable>

        <xsl:variable name="CodeStr">
          <xsl:value-of select="Code" />
        </xsl:variable>

        <xsl:if test="string-length($CodeStr) != 0">
          <xsl:value-of select="concat('4=', $CodeStr)"/>
          <xsl:call-template name="NewLine"/>
        </xsl:if>
        <xsl:if test="$NthStr != '?'">
          <xsl:value-of select="concat('37=', $NthStr)"/>
          <xsl:call-template name="NewLine"/>
        </xsl:if>
        <xsl:if test="$EastStr != '?'">
          <xsl:value-of select="concat('38=', $EastStr)"/>
          <xsl:call-template name="NewLine"/>
        </xsl:if>
        <xsl:if test="$ElevStr != '?'">
          <xsl:value-of select="concat('39=', $ElevStr)"/> 
          <xsl:call-template name="NewLine"/>
        </xsl:if>
      </xsl:if>
    </xsl:for-each>
  </xsl:if>

  <!-- TGO doesn't like a note in the data at this point so skip this data
  <xsl:value-of select="concat('0=Sf:', $StnSF)"/>
  <xsl:call-template name="NewLine"/>
   -->
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** BackBearingRecord Output ********************* -->
<!-- **************************************************************** -->
<xsl:template match="BackBearingRecord">
  <xsl:variable name="StnStr">
    <xsl:value-of select="Station" />
  </xsl:variable>

  <xsl:variable name="BSStr">
    <xsl:value-of select="BackSight" />
  </xsl:variable>

  <xsl:variable name="OrientStr">
    <xsl:call-template name="AngleValue">
      <xsl:with-param name="TheAngle">
        <xsl:value-of select="OrientationCorrection"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="BSObsStr">
    <xsl:call-template name="AngleValue">
      <xsl:with-param name="TheAngle">
        <xsl:value-of select="Face1HorizontalCircle"/>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:variable>

  <xsl:value-of select="concat('62=', $BSStr)"/>
  <xsl:call-template name="NewLine"/>
  <xsl:value-of select="concat('21=', $BSObsStr)"/>
  <xsl:call-template name="NewLine"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** Attached Note Output ********************** -->
<!-- **************************************************************** -->
<xsl:template match="Notes">
  <!-- Process all notes attached to the current record -->
  <xsl:for-each select="current()/Note">
    <xsl:value-of select="'0='"/>
    <xsl:value-of select="current()"/>
    <xsl:call-template name="NewLine"/>
  </xsl:for-each>  
</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** Format a DMS Angle ********************** -->
<!-- **************************************************************** -->
<xsl:template name="FormatDMSAngle">
  <xsl:param name="DecimalAngle"/>

  <xsl:variable name="Sign">
    <xsl:if test="$DecimalAngle &lt; '0.0'">-1</xsl:if>
    <xsl:if test="$DecimalAngle &gt;= '0.0'">1</xsl:if>
  </xsl:variable>

  <xsl:variable name="PosDecimalDegrees" select="number($DecimalAngle * $Sign)"/>

  <xsl:variable name="PositiveDecimalDegrees">  <!-- Ensure an angle very close to 360° is treated as 0° -->
    <xsl:choose>
      <xsl:when test="(360.0 - $PosDecimalDegrees) &lt; 0.00001">
        <xsl:value-of select="0"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$PosDecimalDegrees"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="Degrees" select="floor($PositiveDecimalDegrees)"/>
  <xsl:variable name="DecimalMinutes" select="number(number($PositiveDecimalDegrees - $Degrees) * 60 )"/>
  <xsl:variable name="Minutes" select="floor($DecimalMinutes)"/>
  <xsl:variable name="Seconds" select="number(number($DecimalMinutes - $Minutes)*60)"/>

  <!-- Output seconds values to a tenth of a second so multiply the seconds value by 10 -->
  <xsl:variable name="PartiallyNormalisedMinutes">
    <xsl:if test="format-number($Seconds * 10, '000') = '600'"><xsl:value-of select="number($Minutes + 1)"/></xsl:if>
    <xsl:if test="not(format-number($Seconds * 10, '000') = '600')"><xsl:value-of select="$Minutes"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedSeconds">
    <xsl:if test="format-number($Seconds * 10, '000') = '600'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($Seconds * 10, '000') = '600')"><xsl:value-of select="$Seconds * 10"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="PartiallyNormalisedDegrees">
    <xsl:if test="format-number($PartiallyNormalisedMinutes, '00') = '60'"><xsl:value-of select="number($Degrees + 1)"/></xsl:if>
    <xsl:if test="not(format-number($PartiallyNormalisedMinutes, '00') = '60')"><xsl:value-of select="$Degrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedDegrees">
    <xsl:if test="format-number($PartiallyNormalisedDegrees, '0') = '360'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($PartiallyNormalisedDegrees, '0') = '360')"><xsl:value-of select="$PartiallyNormalisedDegrees"/></xsl:if>
  </xsl:variable>

  <xsl:variable name="NormalisedMinutes">
    <xsl:if test="format-number($PartiallyNormalisedMinutes, '00') = '60'"><xsl:value-of select="0"/></xsl:if>
    <xsl:if test="not(format-number($PartiallyNormalisedMinutes, '00') = '60')"><xsl:value-of select="$PartiallyNormalisedMinutes"/></xsl:if>
  </xsl:variable>

  <xsl:if test="$Sign = -1">-</xsl:if>
  <xsl:value-of select="format-number($NormalisedDegrees, '0')"/>
  <xsl:value-of select="$DegreesSymbol"/>
  <xsl:value-of select="format-number($NormalisedMinutes, '00')"/>
  <xsl:value-of select="$MinutesSymbol"/>
  <xsl:value-of select="format-number($NormalisedSeconds, '000')"/>
  <xsl:value-of select="$SecondsSymbol"/>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************ Output Angle in Appropriate Format **************** -->
<!-- **************************************************************** -->
<xsl:template name="AngleValue">
  <xsl:param name="TheAngle"/>
  <xsl:param name="deltaAngle" select="'False'"/>
  <xsl:choose>
    <!-- Null angle value -->
    <xsl:when test="string(number($TheAngle))='NaN'">
      <xsl:value-of select="'?'"/>
    </xsl:when>
    <!-- There is an angle value -->
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$AngleUnit='Gons'">
          <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl5, 'Standard')"/>
        </xsl:when>

        <xsl:when test="$AngleUnit='Mils'">
          <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl4, 'Standard')"/>
        </xsl:when>

        <xsl:when test="$AngleUnit='DecimalDegrees'">
          <xsl:value-of select="format-number($TheAngle * $AngleConvFactor, $DecPl5, 'Standard')"/>
        </xsl:when>

        <xsl:otherwise>
          <xsl:call-template name="FormatDMSAngle">
            <xsl:with-param name="DecimalAngle" select="$TheAngle"/>
          </xsl:call-template>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Feature and Attributes Output ****************** -->
<!-- **************************************************************** -->
<xsl:template match="Features">

  <!-- Output attributes if they are named 90..99 (User labels) -->
  <xsl:for-each select="Feature">
    <xsl:for-each select="Attribute">
      <xsl:if test="(number(Name) &gt; 89) and (number(Name) &lt; 100)">
        <xsl:value-of select="Name"/>
        <xsl:value-of select="'='"/>
        <xsl:value-of select="Value"/>
        <xsl:call-template name="NewLine"/>
      </xsl:if>
    </xsl:for-each>
  </xsl:for-each>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


</xsl:stylesheet>